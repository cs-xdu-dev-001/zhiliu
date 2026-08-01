import { Route, Switch } from "wouter";

import { AppShell } from "./components/AppShell";
import { Login } from "./pages/Login";

export function App() {
  return <Switch><Route path="/login" component={Login} /><Route><AppShell /></Route></Switch>;
}

