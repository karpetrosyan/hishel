import { CachedResponse } from "../types"


export default function RequestInfo(response: CachedResponse) {
    return <>{response.request.url}</>
}