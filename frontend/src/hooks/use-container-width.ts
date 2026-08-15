import { useRef, useState, useEffect, useCallback } from 'react';

export function useContainerWidth(defaultWidth = 600): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(defaultWidth);

  const updateWidth = useCallback(() => {
    if (ref.current) {
      const measured = ref.current.getBoundingClientRect().width;
      if (measured > 0) setWidth(Math.floor(measured));
    }
  }, []);

  useEffect(() => {
    updateWidth();
    if (!ref.current) return;

    const observer = new ResizeObserver(updateWidth);
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [updateWidth]);

  return [ref, width];
}
