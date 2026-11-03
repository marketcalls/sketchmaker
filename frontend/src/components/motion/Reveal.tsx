import { motion, useReducedMotion } from 'motion/react';
import type { ReactNode } from 'react';
import { studioEase } from './transitions';

interface RevealProps {
  children: ReactNode;
  className?: string;
  /** Seconds to wait before animating in. */
  delay?: number;
  /** Direction the element travels from. */
  from?: 'up' | 'down' | 'left' | 'right' | 'none';
  /** Travel distance in px. */
  distance?: number;
  /** Animate once when scrolled into view (default) or on every entry. */
  once?: boolean;
  duration?: number;
}

const offsets = {
  up: (d: number) => ({ y: d }),
  down: (d: number) => ({ y: -d }),
  left: (d: number) => ({ x: d }),
  right: (d: number) => ({ x: -d }),
  none: () => ({}),
};

/** Scroll-triggered reveal. Use for sections, cards, and headings. */
export function Reveal({
  children,
  className,
  delay = 0,
  from = 'up',
  distance = 8,
  once = true,
  duration = 0.35,
}: RevealProps) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;

  return (
    <motion.div
      className={className}
      // Capped so no caller can bring back large, slow entrances.
      initial={{ opacity: 0, ...offsets[from](Math.min(distance, 8)) }}
      whileInView={{ opacity: 1, x: 0, y: 0 }}
      viewport={{ once, margin: '0px 0px -60px 0px' }}
      transition={{ duration: Math.min(duration, 0.4), delay: Math.min(delay, 0.2), ease: studioEase }}
    >
      {children}
    </motion.div>
  );
}
