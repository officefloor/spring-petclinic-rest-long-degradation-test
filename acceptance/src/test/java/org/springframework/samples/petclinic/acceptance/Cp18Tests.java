package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

/** cp18: an owner may have at most 6 pets. */
@Tag("cp18")
class Cp18Tests extends AcceptanceBase {

	@Test
	void coreRejectsSeventhPet() throws Exception {
		int id = createOwnerOk(validOwner());
		for (int i = 1; i <= 6; i++) {
			addPet(id, validPet("Pet" + i)).andExpect(status().is2xxSuccessful());
		}
		addPet(id, validPet("Pet7")).andExpect(status().isBadRequest());
	}

	@Test
	void functionalityAllowsSixthPet() throws Exception {
		int id = createOwnerOk(validOwner());
		for (int i = 1; i <= 5; i++) {
			addPet(id, validPet("P" + i)).andExpect(status().is2xxSuccessful());
		}
		addPet(id, validPet("P6")).andExpect(status().is2xxSuccessful());
	}
}
