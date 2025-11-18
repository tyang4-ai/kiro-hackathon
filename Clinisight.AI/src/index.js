const ForgeUI = require('@forge/ui');
const { render, Fragment, Text, Strong } = ForgeUI;

exports.handler = render(
  <Fragment>
    <Strong>Clinisight.AI Healthcare Intelligence</Strong>
    <Text>🏥 Welcome to your clinical command center!</Text>
    <Text>Status: System Online</Text>
  </Fragment>
);