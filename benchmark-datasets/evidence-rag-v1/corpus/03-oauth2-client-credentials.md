# OAuth2 client credentials (machine-to-machine)

The **client credentials** grant is suited for confidential clients acting on their own behalf—cron jobs, workers, or backend services—not an end user. The client authenticates with the authorization server using **client_id and client_secret to the token endpoint** (often via HTTP Basic or a form body, depending on server policy).

The token response includes an access token scoped to what the resource owner (or admin) granted the client. Clients must store secrets outside source control and rotate credentials on compromise. This flow does not provide refresh tokens in many deployments; clients obtain a new access token when the current one expires.
