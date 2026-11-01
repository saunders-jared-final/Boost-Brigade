import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import react from '@astrojs/react';

// Deployed at https://saunders-jared-final.github.io/Boost-Brigade/
export default defineConfig({
  site: 'https://saunders-jared-final.github.io',
  base: '/Boost-Brigade',
  trailingSlash: 'ignore',
  integrations: [mdx(), react()],
  markdown: {
    shikiConfig: { themes: { light: 'github-light', dark: 'github-dark' } },
  },
  vite: {
    // Allow build-time reads of repo files one level up (code snippets, READMEs).
    server: { fs: { allow: ['..'] } },
  },
});
