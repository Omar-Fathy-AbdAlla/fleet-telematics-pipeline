import { Line } from '@react-three/drei'
import { useMemo } from 'react'
import * as THREE from 'three'
import { useTheme } from '../hooks/useTheme'
import { MARKER_COLOR } from './MapCanvas'
import { MAP_SCALE, project } from './projection'

const SEGMENTS = 32

// One arc per lane (rows need origin_/destination_ latitude + longitude).
// heightOf(lane) (in degrees, scaled like the map) and colorOf(lane) decide what the arc encodes;
// onHover(lane | null) reports the pointed lane.
export default function RouteArcs({ lanes, heightOf, colorOf, onHover }) {
  const { theme } = useTheme()
  const arcs = useMemo(
    () =>
      lanes.map((lane) => {
        const start = new THREE.Vector3(...project(lane.origin_latitude, lane.origin_longitude))
        const end = new THREE.Vector3(...project(lane.destination_latitude, lane.destination_longitude))
        const control = start.clone().lerp(end, 0.5).setY(heightOf(lane) * MAP_SCALE)
        return { lane, color: colorOf(lane), points: new THREE.QuadraticBezierCurve3(start, control, end).getPoints(SEGMENTS) }
      }),
    [lanes, heightOf, colorOf],
  )

  const cities = useMemo(() => {
    const unique = new Map(lanes.map((lane) => [lane.origin_city, project(lane.origin_latitude, lane.origin_longitude)]))
    return [...unique]
  }, [lanes])

  return (
    <group>
      {arcs.map(({ lane, color, points }) => (
        <Line
          key={lane.route_id}
          points={points}
          color={color}
          lineWidth={1.5}
          onPointerOver={(event) => {
            event.stopPropagation()
            onHover(lane)
          }}
          onPointerOut={() => onHover(null)}
        />
      ))}
      {cities.map(([city, position]) => (
        <mesh key={city} position={position}>
          <sphereGeometry args={[0.2 * MAP_SCALE, 12, 12]} />
          <meshStandardMaterial color={MARKER_COLOR[theme]} />
        </mesh>
      ))}
    </group>
  )
}
