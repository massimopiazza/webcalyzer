import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";
import { TooltipProvider } from "./components/ui/tooltip";
import { SidebarProvider } from "./lib/sidebar";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <SidebarProvider>
        <TooltipProvider delayDuration={250} skipDelayDuration={150}>
          <App />
        </TooltipProvider>
      </SidebarProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
