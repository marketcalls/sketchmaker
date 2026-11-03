import { useEffect, useRef } from 'react';
import { useInView, useMotionValue, useSpring } from 'motion/react';

interface AnimatedNumberProps {
  value: number;
  className?: string;
  /** Format the displayed number (default: integer with locale separators). */
  format?: (n: number) => string;
}

/** Spring-animated counter for stats and prices. */
export function AnimatedNumber({ value, className, format }: AnimatedNumberProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const motionValue = useMotionValue(0);
  const spring = useSpring(motionValue, { stiffness: 90, damping: 24 });

  useEffect(() => {
    if (inView) motionValue.set(value);
  }, [inView, value, motionValue]);

  useEffect(() => {
    const fmt = format ?? ((n: number) => Math.round(n).toLocaleString());
    const unsubscribe = spring.on('change', (latest) => {
      if (ref.current) ref.current.textContent = fmt(latest);
    });
    return unsubscribe;
  }, [spring, format]);

  return (
    <span ref={ref} className={className}>
      {(format ?? ((n: number) => Math.round(n).toLocaleString()))(0)}
    </span>
  );
}
