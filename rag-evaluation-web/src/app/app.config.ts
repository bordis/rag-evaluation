import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { includeBearerTokenInterceptor } from 'keycloak-angular';

import { routes } from './app.routes';
import { provideAutenticacao } from './auth/autenticacao';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideAutenticacao(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withInterceptors([includeBearerTokenInterceptor])),
  ],
};
