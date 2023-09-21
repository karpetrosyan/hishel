import { useState } from "react";
import RequestInfo from "./RequestInfo";
import MetadataInfo from "./MetadataInfo";
import ResponseInfo from "./ResponseInfo";

type Menu = "Request" | "Response" | "Metadata";
import { CachedResponse } from "../types";


export default function Response(
    response: CachedResponse
) {
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

        { selectedMenu === "Request" && <RequestInfo ></RequestInfo>}
        { selectedMenu === "Response" && <ResponseInfo></ResponseInfo>}
        { selectedMenu === "Metadata" && <MetadataInfo></MetadataInfo>}
    </>

  );
}
