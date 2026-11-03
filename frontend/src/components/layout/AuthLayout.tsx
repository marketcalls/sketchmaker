import { Outlet, Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { Sparkles } from 'lucide-react';
import { studioEase } from '@/components/motion';
import { SEO } from '@/components/SEO';

export function AuthLayout() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background p-4">
      <SEO />
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.2, ease: studioEase }}
        className="w-full max-w-md"
      >
        <div className="mb-8 flex justify-center">
          <Link
            to="/"
            className="flex items-center gap-2.5 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            <Sparkles className="h-6 w-6 text-primary" aria-hidden="true" />
            <span className="font-display text-3xl leading-none tracking-tight">Sketchmaker</span>
          </Link>
        </div>

        <Outlet />
      </motion.div>
    </div>
  );
}
