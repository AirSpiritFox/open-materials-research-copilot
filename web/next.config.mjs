const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";
export default { output: "export", trailingSlash: true, basePath, images: {unoptimized: true}, poweredByHeader: false };
