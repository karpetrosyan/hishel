import { CachedResponse } from "../types";

type RequestInfoProps = {
  response: CachedResponse;
};

export default function ResponseInfo({response}: RequestInfoProps) {
  const responseLine = `${response.response.extensions.http_version} ${response.response.status} ${response.response.extensions.reason_phrase}`
  
  return <>
  {responseLine}
  <ol>
    {response.response.headers.map(([key,  value]) => (
      <li>
        <h3>
          <span className="font-bold">{key}</span>: {value}
        </h3>
      </li>
    ))}
  </ol>
  </>;
}
