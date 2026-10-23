# Request conversations and unread messages

Customers and business staff can exchange plain-text messages on a customer-owned service request. Messages stay separate from private Admin notes and follow-up reminders. No email, push, SMS or automatic refresh is enabled.

## Customer

In **My requests**, choose **Follow up** or the unread reply link. Read the shared **Conversation**, enter a follow-up and choose **Send follow-up**. Business replies show the sender's name, **Business reply**, and a timestamp. New business replies add unread badges to My requests and the relevant request row. Your own messages do not count as unread.

## Admin

Choose the request's business under **Switch business**, then open **Customer requests**. Customer messages have a message link and, when applicable, an unread count. Open the request's **Conversation with customer**. Type into **Reply to customer**, review the **Customer-visible** label, then choose **Send reply**. The reply appears in the customer's request conversation. **Internal notes** and **Assignment & follow-up** remain staff-only. Guest requests without a linked customer portal account use their existing email/phone instead; no portal reply form is shown.

## Reading and refreshing

Unread indicators update when the page is refreshed or navigated. Opening a page does not mark it read. Choose **Mark displayed messages as read** after reviewing the messages on the current page. Only the displayed unread messages from the other side are marked for your account. Older pages and messages arriving after that page was loaded remain unread. Each staff member has an independent read state. Newest messages appear first, 25 per page; use Older/Newer messages to navigate. A previously issued read action can be repeated safely.

## Rules and safety

Messages accept 1–2,000 characters of escaped plain text. Validation retains input and identifies errors. A signed submission token expires after one hour; reopen the request if it expires. Current session, role, business membership, customer ownership/profile, CSRF and origin are checked on the server; writes recheck access inside an immediate transaction. Replies and customer messages are saved atomically with an activity entry and use unique submission keys to prevent duplicates, including concurrent replay. Reply and read tokens cannot be interchanged. Read snapshots bind up to 25 displayed message IDs to the viewer, role, request and business. Per-account/IP rate limits apply.

Closed requests still accept messages without reopening. Messages never change the request's status/version, contact snapshot, appointment or private notes. Keep payment details and sensitive records out of conversations.

## Storage and upgrade

The existing customer_request_messages table is extended additively with sender_kind (legacy rows default to customer) and staff_user_id. customer_user_id always identifies the request's customer, including for business replies. request_message_reads stores per-user/per-message receipts. Existing message fields and request data are preserved. Online SQLite backups include conversations and receipts; source archives exclude runtime data, keys and credentials.
