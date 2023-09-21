import { CachedResponse } from "../types";

type RequestInfoProps = {
  response: CachedResponse;
};

export default function RequestInfo({ response }: RequestInfoProps) {
  const requestLine = `${response.request.method} ${response.request.url} ${response.response.extensions.http_version}`

  return <>
  {requestLine}
  <ol>
    {response.request.headers.map(([key,  value]) => (
      <li>
        <h3>
          <span className="font-bold">{key}</span>: {value}
        </h3>
      </li>
    ))}
  </ol>
  </>;
}
