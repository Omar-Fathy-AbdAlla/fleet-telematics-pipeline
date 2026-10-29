import { MAP_BOUNDS } from '../data/facilities'

// Flat lat/lon -> scene projection centered on the data area. MAP_SCALE scene units = 1 degree of latitude (~69 mi).
// Accurate enough at country scale for a visual map (not for distance math).
// MAP_SCALE = map size against the trucks (trucks keep their size): bigger = more space between trucks.
export const MAP_SCALE = 3
const MAP_PADDING = 1 // degrees around MAP_BOUNDS, so facilities on the edge are not on the border of the map

// The area the map shows (degrees): MAP_BOUNDS from the warehouse + MAP_PADDING.
export const MAP_AREA = {
  min_lat: MAP_BOUNDS.min_lat - MAP_PADDING,
  max_lat: MAP_BOUNDS.max_lat + MAP_PADDING,
  min_lon: MAP_BOUNDS.min_lon - MAP_PADDING,
  max_lon: MAP_BOUNDS.max_lon + MAP_PADDING,
}

const CENTER_LAT = (MAP_AREA.min_lat + MAP_AREA.max_lat) / 2
const CENTER_LON = (MAP_AREA.min_lon + MAP_AREA.max_lon) / 2
const LON_SCALE = Math.cos((CENTER_LAT * Math.PI) / 180)

export function project(lat, lon, y = 0) {
  return [(lon - CENTER_LON) * LON_SCALE * MAP_SCALE, y, -(lat - CENTER_LAT) * MAP_SCALE]
}
