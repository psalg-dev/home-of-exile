describe('PoB import', () => {
  it('happy path renders parsed output', () => {
    cy.intercept('POST', '/api/import/pob', {
      statusCode: 200,
      body: {
        character: { class: 'Witch', ascendancy: 'Occultist', level: 92 },
        mainSkill: { name: 'Freezing Pulse', group: 'Main', supportGems: ['Spell Echo'], confidence: 'HIGH' },
        equipment: [{ slot: 'Weapon Slot', name: 'Void Sceptre', rarity: 'RARE', raw: '...' }],
        raw: { warnings: [], source: 'POB_EXPORT_CODE' }
      }
    }).as('import')

    cy.visit('/')

    cy.get('[data-cy=pob-export-code]').type('abc123', { delay: 0 })
    cy.get('[data-cy=pob-import]').click()

    cy.wait('@import')

    cy.get('[data-cy=pob-character]').should('contain.text', 'Witch')
    cy.get('[data-cy=pob-main-skill]').should('contain.text', 'Freezing Pulse')
    cy.get('[data-cy=pob-equipment]').should('contain.text', 'Weapon Slot')
  })

  it('real PoB import categorizes equipment slots (cws-witch)', () => {
    // This test requires the backend to be running at http://localhost:8080 (Vite proxies /api).
    cy.intercept('POST', '/api/import/pob').as('import')

    cy.visit('/')

    cy.readFile('../backend/src/test/resources/cws-witch.txt', 'utf8').then((exportCode) => {
      cy.get('[data-cy=pob-export-code]')
        .invoke('val', exportCode)
        .trigger('input')
    })

    cy.get('[data-cy=pob-import]').click()
    cy.wait('@import').its('response.statusCode').should('eq', 200)

    cy.get('[data-cy=pob-equipment]').should('not.contain.text', 'Unknown slot')
    cy.get('[data-cy=pob-equipment]').should('contain.text', 'Jewel Slot')
    cy.get('[data-cy=pob-equipment]').should('contain.text', 'Amulet Slot')
    cy.get('[data-cy=pob-equipment]').should('contain.text', 'Flask Slot')
    cy.get('[data-cy=pob-equipment]').should('not.contain.text', 'Flask Slot (')
  })

  it('error path shows message and preserves textarea', () => {
    cy.intercept('POST', '/api/import/pob', {
      statusCode: 400,
      body: {
        error: {
          code: 'INVALID_POB_EXPORT_CODE',
          message: 'Could not decode or parse the Path of Building export code',
          details: ['base64 decode failed']
        }
      }
    }).as('import')

    cy.visit('/')

    cy.get('[data-cy=pob-export-code]').type('not-base64', { delay: 0 })
    cy.get('[data-cy=pob-import]').click()

    cy.wait('@import')

    cy.get('[data-cy=pob-error]').should('contain.text', 'Could not decode')
    cy.get('[data-cy=pob-export-code]').should('have.value', 'not-base64')
  })

  it('loading disables button during request', () => {
    cy.intercept('POST', '/api/import/pob', (req) => {
      req.on('response', (res) => {
        res.setDelay(300)
      })
      req.reply({
        statusCode: 200,
        body: {
          character: { class: 'Ranger', level: 90 },
          mainSkill: { name: 'Lightning Arrow', group: 'Main', supportGems: [], confidence: 'LOW' },
          equipment: [],
          raw: { warnings: [], source: 'POB_EXPORT_CODE' }
        }
      })
    }).as('import')

    cy.visit('/')

    cy.get('[data-cy=pob-export-code]').type('abc123', { delay: 0 })
    cy.get('[data-cy=pob-import]').click()

    cy.get('[data-cy=pob-import]').should('be.disabled')
    cy.wait('@import')
    cy.get('[data-cy=pob-import]').should('not.be.disabled')
  })
})
