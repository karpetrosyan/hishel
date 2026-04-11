import { defineConfig } from "vitepress";
import { withMermaid } from "vitepress-plugin-mermaid";

export default defineConfig({
  base: '/hishel/',
  mermaid: {},
  title: "Hishel",
  description: "An elegant HTTP caching library for Python",
  head: [
    [
      "link",
      {
        rel: "icon",
        type: "image/x-icon",
        href: "/favicon.ico",
      },
    ],
  ],
  themeConfig: {
    siteTitle: "Hishel",
    search: {
      provider: "local",
    },
    nav: [],
    sidebar: [
      {
        text: "Introduction",
        items: [
          { text: "Overview", link: "/overview" },
          { text: "Quickstart", link: "/quickstart" },
        ],
      },
      {
        text: "User Guide",
        items: [
          { text: "Proxies", link: "/proxies" },
          { text: "Sans-IO", link: "/sans-io" },
          { text: "Metadata", link: "/metadata" },
          { text: "Policies", link: "/policies" },
        ],
      },
      {
        text: "Integrations",
        items: [
          { text: "HTTPX", link: "/httpx" },
          { text: "Requests", link: "/requests" },
          { text: "FastAPI", link: "/fastapi" },
        ],
      },
    ],
    socialLinks: [
      { icon: "github", link: "https://github.com/karpetrosyan/hishel" },
      {
        icon: {
          svg: '<svg role="img" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><title>PyPI</title><path d="M12.002 0C5.926 0 6.225 2.656 6.225 2.656l.007 2.752h5.873v.826H3.94S0 5.789 0 11.912c0 6.121 3.376 5.904 3.376 5.904h2.016v-2.84s-.109-3.376 3.32-3.376h5.723s3.21.052 3.21-3.103V3.103S18.186 0 12.002 0zM8.812 1.79a1.039 1.039 0 1 1 0 2.077 1.039 1.039 0 0 1 0-2.077zm3.19 22.21c6.076 0 5.777-2.656 5.777-2.656l-.007-2.752h-5.873v-.826h8.165S24 18.211 24 12.088c0-6.121-3.376-5.904-3.376-5.904h-2.016v2.84s.109 3.376-3.32 3.376H9.565s-3.21-.052-3.21 3.103v5.199s-.457 3.098 5.647 3.098zm3.19-1.79a1.039 1.039 0 1 1 0-2.077 1.039 1.039 0 0 1 0 2.077z"/></svg>',
        },
        link: "https://pypi.org/project/hishel/",
      },
    ],
  },
});
