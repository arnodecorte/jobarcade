import type { Job } from "./api";

export function buildFollowUpEmail(job: Job, hiringManager: string): { subject: string; body: string } {
  const appliedAt = job.applied_at ? job.applied_at.replace(" ", "T") : null;
  const appliedDate = appliedAt
    ? new Date(appliedAt).toLocaleDateString("en-NL", { day: "numeric", month: "long", year: "numeric" })
    : "recently";

  const greeting = hiringManager.trim() ? `Dear ${hiringManager.trim()},` : "Dear Hiring Team,";
  const subject = `Follow-up: ${job.title} Application`;
  const body = `${greeting}

I hope this message finds you well. I am writing to follow up on my application for the ${job.title} position at ${job.company}, which I submitted on ${appliedDate}.

I remain very enthusiastic about this opportunity and would love to discuss how my background could contribute to your team. Could you kindly provide an update on the status of my application?

Thank you for your time and consideration.

Kind regards,
[Your Name]`;

  return { subject, body };
}
