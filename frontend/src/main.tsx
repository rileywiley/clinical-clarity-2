import React from "react";
import ReactDOM from "react-dom/client";
import {
  createBrowserRouter,
  RouterProvider,
} from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./index.css";
import "./print.css";

const queryClient = new QueryClient();

// Data router (required for useBlocker). All routing lives inside <App />'s
// <Routes> — we mount it under a single splat route so the in-app `<Routes>`
// can still describe each page.
const router = createBrowserRouter([
  { path: "*", element: <App /> },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>,
);
