import {test,expect} from '@playwright/test';
test('acknowledge alert with note',async({page})=>{
 await page.goto('/');await page.getByTestId('user').fill('cg1');await page.locator('input[type=password]').fill('Demo-Pass-123');await page.getByTestId('login').click();
 await page.getByTestId('pat-p1').click();
 await page.getByPlaceholder('Note').fill('called family');await page.getByRole('button',{name:'Acknowledge'}).click();
 await expect(page.getByTestId('alert').first()).toContainText('called family');
});
