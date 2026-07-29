import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClientModule } from '@angular/common/http';

import { ProductListComponent } from './product-list/product-list.component';
import { ProductDetailComponent } from './product-detail/product-detail.component';
import { CartComponent } from './cart/cart.component';

/**
 * Storefront feature module wiring the PLP, PDP and Cart components.
 * (Pure framework glue — the migrator should Skip this, with a reason.)
 */
@NgModule({
  declarations: [ProductListComponent, ProductDetailComponent, CartComponent],
  imports: [CommonModule, HttpClientModule],
  exports: [ProductListComponent, ProductDetailComponent, CartComponent],
})
export class StorefrontModule {}
