"""Live validations that drive the **served** surface rather than raw Gmail.

Separate from `preflight`, which measures Gmail itself. A validation here answers "what does
MailWeave do against a real mailbox under a named setting", which is a question about this
server and not about the API underneath it.
"""
