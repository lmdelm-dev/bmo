// @ts-nocheck
/** @jsxImportSource @opentui/solid */
import type { TuiPlugin, TuiThemeCurrent } from "@opencode-ai/plugin/tui";
import { createMemo } from "solid-js";

const BMO_ART = [
  "██████╗ ███╗   ███╗ ██████╗",
  "██╔══██╗████╗ ████║██╔═══██╗",
  "██████╔╝██╔████╔██║██║   ██║",
  "██╔══██╗██║╚██╔╝██║██║   ██║",
  "██████╔╝██║ ╚═╝ ██║╚██████╔╝",
  "╚═════╝ ╚═╝     ╚═╝ ╚═════╝ ",
];

const TAG = "LMDELM-dev";

const Logo = (props: { theme: TuiThemeCurrent }) => {
  const lines = createMemo(() => BMO_ART);
  const mid = Math.floor(lines().length / 2);
  return (
    <box flexDirection="column">
      {lines().map((line, i) => (
        <box flexDirection="row" alignItems="center">
          <text fg={props.theme.primary}>{line}</text>
          {i === mid && <text fg={props.theme.textMuted}>{`  ${TAG}`}</text>}
        </box>
      ))}
    </box>
  );
};

const tui: TuiPlugin = async (api) => {
  api.slots.register({
    id: "bmo-logo",
    order: 300,
    slots: {
      home_logo(ctx) {
        return <Logo theme={ctx.theme.current} />;
      },
    },
  });
};

const plugin = { id: "opencode-bmo-logo", tui };
export default plugin;
