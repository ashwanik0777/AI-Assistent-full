import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  transpilePackages: ['@aira/types', '@aira/constants', '@aira/api-client'],
};

export default nextConfig;
