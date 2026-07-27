package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp19: an owner cannot have two pets with the same name (add or rename). */
@Tag("cp19")
class Cp19Tests extends AcceptanceBase {

	@Test
	void coreRejectsDuplicatePetNameForSameOwner() throws Exception {
		int id = createOwnerOk(validOwner());
		addPet(id, validPet("Rex")).andExpect(status().is2xxSuccessful());
		addPet(id, validPet("Rex")).andExpect(status().isBadRequest());
	}

	@Test
	void functionalityAllowsSameNameForDifferentOwners() throws Exception {
		int a = createOwnerOk(validOwner());
		addPet(a, validPet("Bella")).andExpect(status().is2xxSuccessful());
		int b = createOwnerOk(validOwner());
		addPet(b, validPet("Bella")).andExpect(status().is2xxSuccessful());
	}

	@Test
	void functionalityRejectsRenameToSiblingName() throws Exception {
		int id = createOwnerOk(validOwner());
		addPet(id, validPet("Milo")).andExpect(status().is2xxSuccessful());
		int petId = extractId(addPet(id, validPet("Nala")).andExpect(status().is2xxSuccessful()));
		ObjectNode rename = validPet("Milo"); // clash with sibling
		updatePet(petId, rename).andExpect(status().isBadRequest());
	}
}
