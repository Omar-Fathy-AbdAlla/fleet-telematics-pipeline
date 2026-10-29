import { FACILITIES } from '../data/facilities'
import { useTheme } from '../hooks/useTheme'
import { MARKER_COLOR } from './MapCanvas'
import { project } from './projection'

// A facility = a small building of two boxes, sizes in scene units [width, height, depth].
// offset = box center from the facility point [x, z]; each box stands on the map (center at half its height).
const OFFICE_COLOR = { light: '#64748b', dark: '#94a3b8' } // lighter / darker than MARKER_COLOR, so the two parts read apart
const PARTS = [
  { name: 'hall', size: [1.4, 1.6, 1.0], offset: [0, 0], color: MARKER_COLOR }, // main hall: wide and low
  { name: 'office', size: [0.6, 3.2, 0.6], offset: [-0.4, -0.2], color: OFFICE_COLOR }, // office block: narrow and tall, back corner
]

// Facility positions are fixed (hardcoded from the warehouse), so they are projected once.
const MARKERS = FACILITIES.map((facility) => ({ facility, position: project(facility.latitude, facility.longitude) }))

// One building per facility (DIM_FACILITY). onHover(facility | null) reports the pointed facility.
export default function FacilityLayer({ onHover }) {
  const { theme } = useTheme()
  return (
    <group>
      {MARKERS.map(({ facility, position }) => (
        <group
          key={facility.facility_id}
          position={position}
          onPointerOver={(event) => {
            event.stopPropagation()
            onHover(facility)
          }}
          onPointerOut={() => onHover(null)}
        >
          {PARTS.map(({ name, size, offset, color }) => (
            <mesh key={name} position={[offset[0], size[1] / 2, offset[1]]}>
              <boxGeometry args={size} />
              <meshStandardMaterial color={color[theme]} />
            </mesh>
          ))}
        </group>
      ))}
    </group>
  )
}
