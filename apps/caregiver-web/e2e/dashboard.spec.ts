import {test,expect} from '@playwright/test';
test('add patient issues PIN; severity shows disclaimer; consent defaults off',async({page})=>{
 await page.goto('/');await page.getByTestId('user').fill('cg1');await page.locator('input[type=password]').fill('Demo-Pass-123');await page.getByTestId('login').click();
 await page.getByPlaceholder('Name').fill('Test Elder');await page.getByLabel('Age',{exact:true}).fill('71');await page.getByTestId('addpat').click();
 await expect(page.getByTestId('pin')).toContainText('4821');
 await page.getByTestId('pat-p1').click();
 await expect(page.getByTestId('disclaimer')).toContainText('not a diagnosis');
 await expect(page.getByTestId('consent-camera')).not.toBeChecked();
 await page.getByTestId('consent-mic').click();await expect(page.getByTestId('consent-mic')).toBeChecked();
});
test('health worker cannot change consent',async({page})=>{
 await page.goto('/');await page.getByTestId('user').fill('hw1');await page.locator('input[type=password]').fill('Demo-Pass-123');await page.getByTestId('login').click();
 await page.getByTestId('pat-p1').click();await expect(page.getByTestId('consent-mic')).toBeDisabled();
});
