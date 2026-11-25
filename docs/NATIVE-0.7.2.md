# Capella 7.1.0 plug-in update 0.7.2

This update pairs with Claude Desktop extension 0.9.2. It fixes `show_element` on a Mode State Machine diagram when the view already represents an in-scope state, mode, or transition. It covers views Sirius projects for nested Regions of a composite state. The connector returns the existing view without inserting another view, refreshing the diagram, changing its presentation, or saving the model.

For new views, direct insertion still requires an element owned by the diagram’s Region and existing endpoint views for a transition. Use Capella’s own diagram tools to display a nested element that is absent from the diagram. Review any existing `unknown_outcome` job separately using [the recovery guide](RECOVER-EDIT.md).

## Install

1. Finish editing and decide which pending model changes to save before restarting Capella. Stop the Independent MCP connector.
2. In Capella 7.1.0, open **Help → Install New Software → Add → Archive** and select `capella-mcp-update-site-0.7.2-capella-7.1.0.zip`.
3. Select the Independent Capella MCP feature, complete the update and follow Capella’s restart prompt. Keep the existing Claude Desktop 0.9.2 extension.
4. Manually pair a disposable model first. Use a fresh snapshot to select an existing MSM representation and a state or transition already shown. Submit one reviewed `show_element` and confirm the job succeeds and the diagram retains its original views.
