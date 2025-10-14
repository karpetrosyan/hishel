# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "hishel[requests]",
# ]
#
# [tool.uv.sources]
# hishel = { path = ".", editable = true }
# ///


from hishel.beta.requests import CacheAdapter

client = SyncCacheClient()
response = client.get("https://hishel.com", extensions={"hishel_spec_ignore": True})
response = client.get("https://hishel.com", extensions={"hishel_spec_ignore": True})
print(response.extensions)
