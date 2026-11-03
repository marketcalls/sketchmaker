import type { Transition, Variants } from 'motion/react';

/** Signature easing for the whole app: a quick start and a soft settle. */
export const studioEase = [0.22, 1, 0.36, 1] as const;

export const springSnappy: Transition = {
  type: 'spring',
  stiffness: 420,
  damping: 32,
  mass: 0.9,
};

export const springSoft: Transition = {
  type: 'spring',
  stiffness: 180,
  damping: 26,
  mass: 1,
};

// Entrances stay gentle: a short fade with at most a few pixels of travel.
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 6 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.3, ease: studioEase },
  },
};

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.25, ease: studioEase } },
};

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.99 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.3, ease: studioEase },
  },
};

export const staggerContainer = (stagger = 0.04, delay = 0): Variants => ({
  hidden: {},
  visible: {
    transition: { staggerChildren: stagger, delayChildren: delay },
  },
});
