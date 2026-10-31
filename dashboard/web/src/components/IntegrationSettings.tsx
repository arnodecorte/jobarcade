import { useState } from "react";
import type { IntegrationStatus } from "../lib/api";
import {
  clearGmailIntegration,
  saveGmailIntegration,
  saveOllamaIntegration,
  testOllamaIntegration,
} from "../lib/api";

type Props = {
  integrations: IntegrationStatus;
  reload: () => void;
};

export function IntegrationSettings({ integrations, reload }: Props) {
  const [message, setMessage] = useState("");
  const [testing, setTesting] = useState(false);

  async function saveGmail(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form).entries()) as Record<string, string>;
    setMessage("Saving Gmail configuration...");
    try {
      await saveGmailIntegration({
        client_id: values.client_id,
        client_secret: values.client_secret,
        redirect_uri: values.redirect_uri,
      });
      form.elements.namedItem("client_secret") &&
        ((form.elements.namedItem("client_secret") as HTMLInputElement).value = "");
      setMessage("Gmail configuration saved securely.");
      reload();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function clearGmail() {
    if (!window.confirm("Remove saved Google credentials and disconnect Gmail?")) return;
    setMessage("Removing Gmail configuration...");
    try {
      await clearGmailIntegration();
      setMessage("Saved Gmail configuration removed.");
      reload();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function saveOllama(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget).entries()) as Record<string, string>;
    setMessage("Saving Ollama configuration...");
    try {
      await saveOllamaIntegration({ base_url: values.base_url, model: values.model });
      setMessage("Ollama configuration saved.");
      reload();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function testOllama() {
    setTesting(true);
    setMessage("Testing Ollama...");
    try {
      const result = await testOllamaIntegration();
      setMessage(
        result.ok
          ? result.model_present
            ? `${result.model} is available.`
            : `Ollama is reachable, but ${result.model} is not installed.`
          : result.error || "Ollama could not be reached.",
      );
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="integration-settings">
      <form onSubmit={saveGmail}>
        <div className="integration-title">
          <div>
            <h3>Gmail OAuth</h3>
            <p>Stored secrets are encrypted and are never displayed again.</p>
          </div>
          <span className={`health ${integrations.gmail.configured ? "ok" : "warning"}`}>
            {integrations.gmail.configured ? "Configured" : "Setup needed"}
          </span>
        </div>
        <ol className="setup-steps">
          <li>Create a Google Cloud Web OAuth client.</li>
          <li>Add the callback URL below to its authorized redirect URIs.</li>
          <li>Paste the client credentials, save, then connect Gmail.</li>
        </ol>
        <label className="field">
          Client ID
          <input name="client_id" required defaultValue={integrations.gmail.client_id} autoComplete="off" />
        </label>
        <label className="field">
          Client secret
          <input
            name="client_secret"
            type="password"
            required={!integrations.gmail.client_secret_set}
            placeholder={integrations.gmail.client_secret_set ? "Saved securely - leave blank to keep" : "Paste client secret"}
            autoComplete="new-password"
          />
        </label>
        <label className="field">
          OAuth callback URL
          <input name="redirect_uri" type="url" required defaultValue={integrations.gmail.redirect_uri} />
        </label>
        <div className="integration-actions">
          <button className="btn rose sm" type="submit">Save Gmail settings</button>
          {integrations.gmail.configured && integrations.gmail.source === "vault" ? (
            <button className="btn ghost sm" type="button" onClick={clearGmail}>Clear credentials</button>
          ) : null}
        </div>
      </form>

      <form onSubmit={saveOllama}>
        <div className="integration-title">
          <div>
            <h3>Ollama</h3>
            <p>Local semantic classification for job-related email.</p>
          </div>
          <span className="health ok">{integrations.ollama.source}</span>
        </div>
        <label className="field">
          Ollama URL
          <input name="base_url" type="url" required defaultValue={integrations.ollama.base_url} />
        </label>
        <label className="field">
          Model
          <input name="model" required defaultValue={integrations.ollama.model} />
        </label>
        <div className="integration-actions">
          <button className="btn rose sm" type="submit">Save Ollama settings</button>
          <button className="btn ghost sm" type="button" onClick={testOllama} disabled={testing}>
            {testing ? "Testing..." : "Test connection"}
          </button>
        </div>
      </form>
      {message ? <p className="integration-message">{message}</p> : null}
    </div>
  );
}
