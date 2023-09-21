import { useState } from "react";
import RequestInfo from "./RequestInfo";
import MetadataInfo from "./MetadataInfo";
import ResponseInfo from "./ResponseInfo";

import { CachedResponse } from "../types";

type Menu = "Request" | "Response" | "Metadata";

type ResponseProps = {
  response: CachedResponse;
};

export default function Response({ response }: ResponseProps) {
  const [selectedMenu, setSelectedMenu] = useState<Menu>("Response");

  return (
    <>
      <nav className="flex px-2 pt-2 bg-gray-100">
        {["Request", "Response", "Metadata"].map((menu) => (
          <h3
            className={`cursor-pointer rounded px-4 ${
              selectedMenu === menu ? "bg-white opacity-100" : "opacity-60"
            }`}
            onClick={() => setSelectedMenu(menu as Menu)}
          >
            {menu}
          </h3>
        ))}
      </nav>

      <div className="p-2 text-gray-700">
        {selectedMenu === "Request" && (
          <RequestInfo response={response}></RequestInfo>
        )}
        {selectedMenu === "Response" && <ResponseInfo response={response}></ResponseInfo>}
        {selectedMenu === "Metadata" && <MetadataInfo response={response}></MetadataInfo>}
      </div>

    </>
  );
}
