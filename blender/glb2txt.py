"""Write a .glb as base64 text (<name>.glb.txt) for the artifact host.

The host serves .txt but not .glb, and its CSP blocks data: URIs, so the page
fetches this text, decodes it and hands the bytes straight to GLTFLoader.parse.
"""
import base64, sys
src, dst = sys.argv[1], sys.argv[2]
data = open(src, 'rb').read()
assert data[:4] == b'glTF', 'not a GLB file'
open(dst, 'w').write(base64.b64encode(data).decode())
print(dst, round(len(data) / 1e6, 2), 'MB glb')
