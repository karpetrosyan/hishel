type a = asdf | AxiosDefaults;

export type CachedResponse = {
    response: {
        status: number,
        headers: [string, string][],
        content: string,
        extensions: {
            [k: string]: string
        }
    },
    request: {
        method: string,
        url: string,
        headers: [string, string][],
        extensions: {timeout : {
            "read": number,
            "write": number,
            connect: number,
            pool: number
        }}
    },
    metadata: {
        cache_key: string,
        number_of_uses: number,
        created_at: string
    }
}

