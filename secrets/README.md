# Demo-exchange credentials go here (this folder is gitignored)

1. Log in at the Kalshi **demo** exchange (demo.kalshi.co) and create an API key
   (account settings -> API keys).
2. Save the key ID as `kalshi_demo_key_id.txt` (one line).
3. Save the private key file Kalshi gives you as `kalshi_demo_private_key.pem`.

`python -m oilx kalshi-demo` reads both. Never put a production key here — the client
refuses to talk to anything but the demo base URL anyway, but don't test that promise.
Never paste the private key into a chat or commit it anywhere.
