# Best Practices & Guidelines for Creating Playwright Locators in Mendix UI Applications

Testing Mendix applications with Playwright requires an understanding of how Mendix generates its DOM structure. Because Mendix is a low-code platform, it dynamically generates HTML elements, class names, and IDs that can change across builds, deployments, or platform upgrades. 

This guide outlines the basic rules and strategies for creating robust, reliable, and maintainable locators for Mendix UI applications.

---

## 1. Avoid Dynamic Mendix Auto-Generated IDs
Mendix frequently generates dynamic IDs for widgets (e.g., `id="mxui_widget_TextInput_0"`, `id="mxui_widget_ReferenceSelector_3"`).
* **Rule:** **Never** use these auto-generated IDs in your locators. They change depending on the execution order, data state, and platform version.
* **Bad Example:** `page.locator('#mxui_widget_TextInput_3')`
* **Good Example:** Using custom classes or test IDs instead.

---

## 2. Leverage the Mendix Class Property (Explicit Naming)
The most reliable way to locate elements in Mendix is to assign a unique, semantic class name to the widget inside the **Mendix Studio Pro** desktop modeler.
* **Rule:** Work with developers to add a specific CSS class (e.g., `test-username-input`, `qa-submit-button`) in the widget's "Class" property.
* **Playwright Locator:**
    ```typescript
    // Locate via the explicit test class
    await page.locator('.test-username-input input').fill('john_doe');
    ```

---

## 3. Use `page.getByRole()` for Semantic Accessibility
Playwright's `getByRole` locator reflects how assistive technologies perceive the page. Even in Mendix, standard buttons, checkboxes, and inputs retain their semantic HTML structures.
* **Rule:** Prioritize user-facing attributes like roles and accessible names over structure.
* **Examples:**
    ```typescript
    // Click a button with text "Save"
    await page.getByRole('button', { name: 'Save' }).click();

    // Check a checkbox labeled "I agree"
    await page.getByRole('checkbox', { name: 'I agree' }).check();
    ```

---

## 4. Use Text and Direct Labels (`getByText`, `getByLabel`)
Mendix UIs are heavy on labels and descriptive texts. Playwright provides built-in locators that hook into visible text, making scripts highly resilient to DOM layout adjustments.
* **Rule:** Use text-based locators for static links, buttons, and form labels.
* **Examples:**
    ```typescript
    // Locate by visible text
    await page.getByText('Order Confirmation').waitFor();

    // Locate a form control by its associated label text
    await page.getByLabel('Email Address').fill('hello@example.com');
    ```

---

## 5. Handle Mendix Layout Grids and Data Views
Mendix wraps components inside heavily nested containers like `mx-grid`, `mx-dataview`, and `mx-listview`. When selecting an item from a list or grid, scope your locators.
* **Rule:** Locate the specific row, card, or container first, then chain the sub-locator.
* **Example (Locating a delete button inside a specific list row):**
    ```typescript
    // Chain locators to find the button inside a specific list item containing 'Item Alpha'
    const listItem = page.locator('.mx-listview-item', { hasText: 'Item Alpha' });
    await listItem.getByRole('button', { name: 'Delete' }).click();
    ```

---

## 6. Beware of Fragile Class Names
Mendix applies multiple built-in utility classes (e.g., `mx-name-textBox1`, `form-group`, `col-md-9`). 
* **Rule:** While `mx-name-[NameInModeler]` (e.g., `mx-name-usernameInput`) is often generated automatically based on the Modeler's element name, it can change if a business analyst renames the element in Studio Pro. 
* **Recommendation:** Treat `mx-name-*` classes with caution. They are safer than auto-generated widget IDs, but custom designated test classes (Rule #2) are always preferred.
* **Example using Modeler name:**
    ```typescript
    // Fallback if custom class is unavailable
    await page.locator('.mx-name-usernameInput input').fill('admin');
    ```

---

## 7. Wait Safely for Mendix Microflows/Nanoflows (Network & Loading States)
Mendix UI interactions often trigger asynchronous Microflows/Nanoflows that display a loading spinner (`.mx-progress`) or overlay.
* **Rule:** Do not hardcode timeouts. Let Playwright handle waiting automatically, or explicitly wait for the loading spinner to disappear before executing the next locator step.
* **Example:**
    ```typescript
    // Wait for Mendix global loading overlay to detach
    await page.locator('.mx-progress').waitFor({ state: 'detached' });
    ```

---

## Summary Checklist for Mendix Locators
1. ❌ **Do Not Use:** `#mxui_widget_...` IDs.
2. ⚠️ **Use with Caution:** `.mx-name-...` classes (subject to change if renamed in modeler).
3.  **Preferred:** `.test-...` / `.qa-...` custom classes added directly in Studio Pro.
4.  **Best Practice:** Playwright user-centric locators (`getByRole`, `getByText`, `getByLabel`).
