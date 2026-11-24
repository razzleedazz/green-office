#!/bin/sh
# Builds the deployable site into dist/.
# site/index.html is a fragment (head content up to </style>, then the body);
# this wraps it in a full HTML document and adds the link-preview tags.
set -eu
cd "$(dirname "$0")"

# Final address of the site. On Vercel this is the production domain automatically;
# set SITE_URL yourself to override (e.g. SITE_URL=https://example.com sh build.sh).
if [ -z "${SITE_URL:-}" ]; then
  if [ -n "${VERCEL_PROJECT_PRODUCTION_URL:-}" ]; then SITE_URL="https://$VERCEL_PROJECT_PRODUCTION_URL"
  else SITE_URL="http://localhost:8000"; fi
fi
TITLE="Alp Yücel — Interactive CV"
DESC="Engineering and finance background. I automate recurring work and build AI products. Walk into the office and sit down at the one computer that is on."

rm -rf dist && mkdir dist
cut=$(grep -n '</style>' site/index.html | head -1 | cut -d: -f1)
{
  cat <<HEAD
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="$DESC">
<meta name="author" content="Alp Yücel">
<meta name="theme-color" content="#0f1a14">
<link rel="canonical" href="$SITE_URL/">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Alp Yücel">
<meta property="og:title" content="$TITLE">
<meta property="og:description" content="$DESC">
<meta property="og:url" content="$SITE_URL/">
<meta property="og:image" content="$SITE_URL/og.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="A dark open-plan office seen from above, with a single desk cluster lit in green.">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="$TITLE">
<meta name="twitter:description" content="$DESC">
<meta name="twitter:image" content="$SITE_URL/og.jpg">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'%3E%3Crect width='48' height='48' rx='11' fill='%232f7d4f'/%3E%3Ctext x='24' y='32' font-family='Arial,sans-serif' font-size='22' font-weight='700' fill='%23fff' text-anchor='middle'%3EAY%3C/text%3E%3C/svg%3E">
HEAD
  head -n "$cut" site/index.html
  printf '</head>\n<body>\n'
  tail -n "+$((cut + 1))" site/index.html
  printf '</body>\n</html>\n'
} > dist/index.html
cp site/*.glb.txt dist/
[ -f site/og.jpg ] && cp site/og.jpg dist/
echo "built dist/ for $SITE_URL"
