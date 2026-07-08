import adapter from '@sveltejs/adapter-node';

const config = {
  kit: {
    adapter: adapter(),
    csp: {
      mode: 'auto',
      directives: {
        'default-src': ['self'],
        'connect-src': ['self', 'https://stats.registrystack.org'],
        'img-src': ['self', 'data:'],
        'script-src': ['self', 'https://stats.registrystack.org'],
        'style-src': ['self', 'unsafe-inline'],
        'font-src': ['self'],
        'frame-ancestors': ['none'],
        'base-uri': ['self'],
        'form-action': ['self']
      }
    }
  }
};

export default config;
