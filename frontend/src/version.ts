/**
 * Sketchmaker Version Information
 * Version follows semantic versioning: MAJOR.MINOR.PATCH
 */

export const VERSION = {
  major: 3,
  minor: 0,
  patch: 0,
  get full() {
    return `${this.major}.${this.minor}.${this.patch}`;
  },
};

export const APP_INFO = {
  name: 'Sketchmaker',
  codename: 'React',
  description: 'Advanced AI-Powered Image Generation Platform',
  copyright: `© 2026 Sketchmaker AI`,
  license: 'AGPL v3',
};

export const getVersionString = () => `v${VERSION.full}`;
export const getFullVersionString = () => `${APP_INFO.name} ${getVersionString()}`;
