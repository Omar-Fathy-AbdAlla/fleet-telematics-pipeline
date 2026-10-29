import { useEffect, useRef } from 'react'
import { dataSource } from '../data'

// Subscribes to one live stream event ('telemetry' | 'reefer' | 'alert' | 'kpis' | 'stream_kpis') while the component is mounted.
export function useStream(eventType, onEvent) {
  const handlerRef = useRef(onEvent)

  useEffect(() => {
    handlerRef.current = onEvent
  })

  useEffect(() => dataSource.subscribe(eventType, (payload) => handlerRef.current(payload)), [eventType])
}
