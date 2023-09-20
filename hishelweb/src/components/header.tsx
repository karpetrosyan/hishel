import { useEffect, useState } from "react";
import githubLogo from "../assets/github-mark.svg";
import versionTagLogo from "../assets/tag-svgrepo-com.svg";

export default function Header() {
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    fetch("https://api.github.com/repos/karosis88/hishel/releases/latest")
      .then((response) => response.json())
      .then((data) => setVersion(data["tag_name"]));
  }, []);

  const zeroOpacity = "opacity-0";

  return (
    <header className="bg-yellow-400 h-10">
      <nav className="mx-96 flex justify-between">
        <a href="" className="leading-10">
          Hishel
        </a>
        <div className="flex">
          <a
            className="flex text-xs items-center hover:opacity-75"
            href="https://github.com/karosis88/hishel"
          >
            <img className="h-6" src={githubLogo} alt="github" />
            <div className="ml-2">
              <div
                className={`flex text-center duration-500 ${
                  version === null ? zeroOpacity : ""
                } `}
              >
                <img className="h-3" src={versionTagLogo} alt="versionTag" />
                <h3 className="leading-3">{version || "0.0.12"}</h3>
              </div>
            </div>
          </a>
        </div>
      </nav>
    </header>
  );
}
