import {test,expect} from '@playwright/test';
test('upload photo -> create reminder',async({page})=>{
 await page.goto('/');await page.getByTestId('user').fill('cg1');await page.locator('input[type=password]').fill('Demo-Pass-123');await page.getByTestId('login').click();
 await page.getByTestId('pat-p1').click();
 await page.getByTestId('photo').setInputFiles({name:'home.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgo=','base64')});
 await expect(page.getByTestId('media')).toContainText('home.png');
 await page.getByTestId('rtitle').fill('Evening water');await page.getByTestId('addrem').click();
 await expect(page.getByTestId('rem').filter({hasText:'Evening water'})).toBeVisible();
});
