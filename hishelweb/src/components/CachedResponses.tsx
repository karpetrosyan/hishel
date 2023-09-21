import { CachedResponse } from "../types";
import Response from "./Response";

export default function CachedResponses() {
  const fakeResponse: CachedResponse = {
    response: {
      status: 200,
      headers: [
        ["Date", "Wed, 20 Sep 2023 08:44:21 GMT"],
        ["Content-Type", "text/html; charset=utf-8"],
        ["Transfer-Encoding", "chunked"],
        ["Connection", "keep-alive"],
        ["Last-Modified", "Fri, 08 Sep 2023 08:25:49 GMT"],
        ["Access-Control-Allow-Origin", "*"],
        ["expires", "Wed, 20 Sep 2023 08:39:11 GMT"],
        ["Cache-Control", "max-age=600"],
        ["x-proxy-cache", "MISS"],
        ["X-GitHub-Request-Id", "C25A:8406:10A5699:111D743:650AAD57"],
        ["Via", "1.1 varnish"],
        ["Age", "36"],
        ["X-Served-By", "cache-fra-eddf8230122-FRA"],
        ["X-Cache", "HIT"],
        ["X-Cache-Hits", "1"],
        ["X-Timer", "S1695199461.406239,VS0,VE1"],
        ["Vary", "Accept-Encoding"],
        ["X-Fastly-Request-ID", "ba8d544cd6f18bd04a8ad8f3c9bb5265456a23d8"],
        ["CF-Cache-Status", "DYNAMIC"],
        [
          "Report-To",
          '{"endpoints":[{"url":"https:\\/\\/a.nel.cloudflare.com\\/report\\/v3?s=Eq1spVuuKqKOydrQ7WTFPcYC1l00mB61RjFe9O5HBaky%2FYCJ4NhH%2FbesqqC0ALU4xRQixZx1MKtIPlUHOuffMUdj4TfEGyxeYuWof%2FERi%2FVInce47NZZd5IUCRVR"}],"group":"cf-nel","max_age":604800}',
        ],
        ["NEL", '{"success_fraction":0,"report_to":"cf-nel","max_age":604800}'],
        ["Server", "cloudflare"],
        ["CF-RAY", "8098c939bfb79bbc-FRA"],
        ["Content-Encoding", "gzip"],
        ["alt-svc", 'h3=":443"; ma=86400'],
      ],
      content:
        "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",
      extensions: {
        http_version: "HTTP/1.1",
        reason_phrase: "OK",
      },
    },
    request: {
      method: "GET",
      url: "https://hishel.com/",
      headers: [
        ["Host", "hishel.com"],
        ["Accept", "*/*"],
        ["Accept-Encoding", "gzip, deflate"],
        ["Connection", "keep-alive"],
        ["User-Agent", "python-httpx/0.24.1"],
      ],
      extensions: {
        timeout: {
          connect: 5.0,
          read: 5.0,
          write: 5.0,
          pool: 5.0,
        },
      },
    },
    metadata: {
      cache_key: "41ebb4dd16761e94e2ee36b71e0d916e",
      number_of_uses: 3,
      created_at: "Wed, 20 Sep 2023 08:44:19 GMT",
    },
  };

  return (
    <section className="">
      {/* <table className="w-7/12 text-gray-800">
        <thead className="bg-gray-100">
          <tr>
            <th className="w-12"></th>
            <th className="font-normal text-left">Path</th>
            <th className="font-normal w-36">Method</th>
            <th className="font-normal w-36">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr className="cursor-pointer hover:bg-slate-300">
            <td></td>
            <td className="text-left">https://hishel.com</td>
            <td className="text-center">GET</td>
            <td className="text-center">200</td>
          </tr>
          <tr className="cursor-pointer hover:bg-slate-300">
            <td></td>
            <td className="text-left">https://hishel.com</td>
            <td className="text-center">GET</td>
            <td className="text-center">200</td>
          </tr>
        </tbody>
      </table> */}

      <Response response={fakeResponse}></Response>
    </section>
  );
}
