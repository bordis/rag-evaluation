import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';

import { Welcome } from './welcome';

describe('Welcome', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Welcome],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('renders the welcome headline and the 3-step explanation', async () => {
    // Arrange
    const fixture = TestBed.createComponent(Welcome);

    // Act
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;

    // Assert
    expect(compiled.querySelector('.hero__title')?.textContent).toContain('melhor');
    expect(compiled.querySelectorAll('.step')).toHaveLength(3);
    expect(compiled.querySelector('.cta')?.textContent).toContain('Começar');
  });
});
