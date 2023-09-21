import { CachedResponse } from "../types";

type MetadataInfoProps = {
  response: CachedResponse;
};


export default function MetadataInfo({response}: MetadataInfoProps) {
  return <>
    <ol>
      <li>
        <h3><span className="font-bold">Created at</span>: {response.metadata.created_at}</h3>
        <h3><span className="font-bold">Number of uses</span>: {response.metadata.number_of_uses}</h3>
        <h3><span className="font-bold">Cache key</span>: {response.metadata.cache_key}</h3>
      </li>
    </ol>
  </>;
}
