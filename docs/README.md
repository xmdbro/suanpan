# Suanpan documentation site

This directory is a dependency-free static site. It can be previewed with any static file server and or deployed pretty simply.

## Set the API URL

Edit `site-config.js` and replace `https://suanpan.example.com` with the production API origin. Every runnable example updates from that one value.

## Preview locally

From the repository root:

```bash
python -m http.server 4173 --directory docs
```

Then open `http://localhost:4173`.