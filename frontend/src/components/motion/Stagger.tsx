import { motion, useReducedMotion } from 'motion/react';
import type { ReactNode } from 'react';
import { fadeUp, staggerContainer } from './transitions';

interface StaggerProps {
  children: ReactNode;
  className?: string;
  /** Seconds between each child. */
  interval?: number;
  /** Seconds before the first child. */
  delay?: number;
  /** Trigger when scrolled into view instead of on mount. */
  onView?: boolean;
}

/** Parent for StaggerItem children — cascading entrance. */
export function Stagger({
  children,
  className,
  interval = 0.04,
  delay = 0,
  onView = false,
}: StaggerProps) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;

  const viewProps = onView
    ? { whileInView: 'visible' as const, viewport: { once: true, margin: '0px 0px -60px 0px' } }
    : { animate: 'visible' as const };

  return (
    <motion.div
      className={className}
      initial="hidden"
      variants={staggerContainer(Math.min(interval, 0.05), Math.min(delay, 0.15))}
      {...viewProps}
    >
      {children}
    </motion.div>
  );
}

export function StaggerItem({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div className={className} variants={fadeUp}>
      {children}
    </motion.div>
  );
}
