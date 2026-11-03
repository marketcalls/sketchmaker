import { motion } from 'motion/react';
import type { ReactNode } from 'react';
import { studioEase } from './transitions';

interface PageTransitionProps {
  children: ReactNode;
  className?: string;
}

/** Wraps a routed page: a short fade on mount, used by layouts keyed on pathname. */
export function PageTransition({ children, className }: PageTransitionProps) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18, ease: studioEase }}
    >
      {children}
    </motion.div>
  );
}
