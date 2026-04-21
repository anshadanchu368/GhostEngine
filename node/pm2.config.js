export default {
  apps: [
    {
      name: 'ghostfabric-node',
      script: 'src/server.js',
      instances: 1,
      exec_mode: 'fork',
      node_args: '--experimental-vm-modules',
      env: {
        NODE_ENV: 'production',
      },
      error_file: '/dev/null',
      out_file: '/dev/null',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      max_memory_restart: '512M',
      watch: false,
      autorestart: true,
      restart_delay: 3000,
    },
  ],
};
