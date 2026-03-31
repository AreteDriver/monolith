#!/bin/bash
# Deploy frontend to Vercel with correct prebuilt output sync
set -e

cd "$(dirname "$0")/../frontend"

SITE_URL="https://aegismonolith.xyz"

echo "▶ Building frontend..."
npm run build

echo "▶ Syncing dist → .vercel/output/static..."
/usr/bin/rm -rf .vercel/output/static
cp -r dist/ .vercel/output/static

echo "▶ Deploying to Vercel..."
npx vercel deploy --prebuilt --prod

echo "▶ Verifying deployment..."
sleep 5
SERVED=$(curl -s "$SITE_URL/" | grep -oP 'src="/assets/index-\K[^.]+' || true)
LOCAL=$(ls dist/assets/index-*.js 2>/dev/null | grep -oP 'index-\K[^.]+' || true)

if [ -n "$SERVED" ] && [ "$SERVED" = "$LOCAL" ]; then
  echo "✓ Verified: bundle $LOCAL is live on $SITE_URL"
else
  echo "⚠ Could not verify bundle hash (served: ${SERVED:-none}, local: ${LOCAL:-none})"
  echo "  Check $SITE_URL manually"
fi
