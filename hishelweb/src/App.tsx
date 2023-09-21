import CachedResponses from "./components/CachedResponses";
import Header from "./components/Header";

export default function App() {
  return (
    <>
      <Header></Header>
      <main className="mt-36 h-20">
        <CachedResponses></CachedResponses>
      </main>
    </>
  );
}
