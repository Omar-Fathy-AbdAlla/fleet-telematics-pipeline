import { useGLTF } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import { useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { STATUS_STYLE, hasPosition, statusOf } from '../hooks/useFleetState'
import { ANOMALY_TYPES } from '../kpis/definitions'
import { MAP_SCALE, project } from './projection'

const CAPACITY = 10_000 // max trucks drawn
const HEIGHT = 0.4 // scene units: truck center above the map, grows with TRUCK_LENGTH so the truck sits on the map
const SCALE = { normal: 1, anomaly: 2.6, selected: 4.5 }
const MODEL_URL = '/models/truck_toyota_corsa_b.glb'
const MODEL_BODY_NODE = 'TOY_CORSB_01_-_Default_0' // textured body; the 10-triangle black part is dropped
const TRUCK_LENGTH = 1 // scene units (~23 mi with MAP_SCALE 3), so the shape reads when zoomed in
const MODEL_YAW = Math.PI // model front is +Z; heading_deg 0 = north = -Z
const SNAP_DISTANCE = MAP_SCALE // scene units (1 degree, ~69 mi): a bigger move is a new trip, so jump instead of gliding across the map
const MAX_INTERVAL_MS = 5000 // cap on the measured batch gap, so a paused tab doesn't make the next glide crawl

// Model body with its node transforms baked in, centered and resized to TRUCK_LENGTH.
function useTruckModel() {
  const { nodes } = useGLTF(MODEL_URL)
  return useMemo(() => {
    const body = nodes[MODEL_BODY_NODE]
    body.updateWorldMatrix(true, false)
    const geometry = body.geometry.clone().applyMatrix4(body.matrixWorld).center()
    geometry.computeBoundingBox()
    const length = geometry.boundingBox.max.z - geometry.boundingBox.min.z
    geometry.scale(TRUCK_LENGTH / length, TRUCK_LENGTH / length, TRUCK_LENGTH / length)
    return { geometry, material: body.material }
  }, [nodes])
}

// Puts `object` at `progress` (0..1) of the way along a truck's segment from -> to ([x, z, yaw]).
function placeAt(object, { from, to }, progress) {
  object.position.set(THREE.MathUtils.lerp(from[0], to[0], progress), HEIGHT, THREE.MathUtils.lerp(from[1], to[1], progress))
  object.rotation.y = THREE.MathUtils.lerp(from[2], to[2], progress)
}

// All trucks as ONE instanced mesh (one draw call). Each new telemetry batch starts a glide from where a truck
// is drawn to its new position, lasting one batch gap, so trucks are drawn ~one batch behind the data.
// hiddenStatuses = Set of statuses not drawn (legend filter); the selected truck is always drawn.
export default function TruckLayer({ fleet, selectedId, hiddenStatuses, onSelect }) {
  const meshRef = useRef()
  const instanceIds = useRef([]) // instance index -> vehicle_id, for clicks
  const segments = useRef(new Map()) // vehicle_id -> { telemetry, from, to, scale }
  const drawn = useRef([]) // instance index -> segment
  const batch = useRef({ at: null, interval: MAX_INTERVAL_MS }) // last telemetry batch time and gap to the one before (ms)
  const settled = useRef(true) // every truck reached its target: no matrices to update
  const { geometry, material } = useTruckModel()
  const dummy = useMemo(() => new THREE.Object3D(), [])
  const colors = useMemo(
    () => Object.fromEntries(Object.entries(STATUS_STYLE).map(([status, style]) => [status, new THREE.Color(style.color)])),
    [],
  )

  useEffect(() => {
    meshRef.current.count = 0 // nothing drawn until the first telemetry batch
  }, [])

  useEffect(() => {
    fleet.dirty.current = true // redraw to highlight the new selection / apply the new filter
  }, [selectedId, hiddenStatuses, fleet.dirty])

  function progressAt(now) {
    const { at, interval } = batch.current
    return at == null ? 1 : Math.min((now - at) / interval, 1)
  }

  // Runs when stream data or the selection changed: new segments for trucks with new telemetry, colors, scales.
  function refresh(mesh, now) {
    const activeTypes = fleet.activeTypesByVehicle()
    const progress = progressAt(now)
    let newBatch = false
    const ids = []
    const list = []
    for (const [vehicleId, { telemetry }] of fleet.vehicles.current) {
      if (!telemetry || ids.length === CAPACITY) continue
      if (!hasPosition(telemetry)) {
        segments.current.delete(vehicleId) // when its position comes back, it appears there instead of gliding from the old spot
        continue
      }
      let segment = segments.current.get(vehicleId)
      if (segment?.telemetry !== telemetry) {
        const [x, , z] = project(telemetry.lat, telemetry.lon)
        const yaw = MODEL_YAW - THREE.MathUtils.degToRad(telemetry.heading_deg ?? 0)
        if (segment) placeAt(dummy, segment, progress) // where the truck is drawn right now
        const glide = segment && Math.hypot(x - dummy.position.x, z - dummy.position.z) <= SNAP_DISTANCE
        const from = glide ? [dummy.position.x, dummy.position.z, dummy.rotation.y] : [x, z, yaw]
        const turn = THREE.MathUtils.euclideanModulo(yaw - from[2] + Math.PI, 2 * Math.PI) - Math.PI // short way round
        segment = { telemetry, from, to: [x, z, from[2] + turn] }
        segments.current.set(vehicleId, segment)
        newBatch = true
      }
      const status = statusOf(telemetry, activeTypes.get(vehicleId))
      // Filtered out in the legend: not drawn (its segment above stays current, so it reappears in the right place).
      if (hiddenStatuses.has(status) && vehicleId !== selectedId) continue
      segment.scale = vehicleId === selectedId ? SCALE.selected : status in ANOMALY_TYPES ? SCALE.anomaly : SCALE.normal
      mesh.setColorAt(ids.length, colors[status])
      ids.push(vehicleId)
      list.push(segment)
    }
    if (newBatch) {
      if (batch.current.at != null) batch.current.interval = Math.min(now - batch.current.at, MAX_INTERVAL_MS)
      batch.current.at = now
    }
    mesh.count = ids.length
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    instanceIds.current = ids
    drawn.current = list
    settled.current = false
  }

  // Every frame while trucks are gliding: move each one along its segment.
  useFrame(() => {
    const mesh = meshRef.current
    const now = performance.now()
    if (fleet.dirty.current) {
      fleet.dirty.current = false
      refresh(mesh, now)
    }
    if (settled.current) return

    const progress = progressAt(now)
    drawn.current.forEach((segment, index) => {
      placeAt(dummy, segment, progress)
      dummy.scale.setScalar(segment.scale)
      dummy.updateMatrix()
      mesh.setMatrixAt(index, dummy.matrix)
    })
    mesh.instanceMatrix.needsUpdate = true
    mesh.boundingSphere = null // trucks moved: recompute bounds so clicks hit the right instance
    settled.current = progress === 1
  })

  return (
    <instancedMesh
      ref={meshRef}
      args={[geometry, material, CAPACITY]}
      frustumCulled={false}
      onClick={(event) => {
        event.stopPropagation()
        onSelect(instanceIds.current[event.instanceId])
      }}
    />
  )
}

useGLTF.preload(MODEL_URL)
