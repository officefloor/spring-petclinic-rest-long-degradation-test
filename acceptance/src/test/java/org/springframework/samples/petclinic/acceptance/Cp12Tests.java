package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp12: optional email; if present, must be a valid format. */
@Tag("cp12")
class Cp12Tests extends AcceptanceBase {

	@Test
	void coreRejectsInvalidEmail() throws Exception {
		ObjectNode o = validOwner();
		o.put("email", "not-an-email");
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void functionalityAcceptsMissingEmail() throws Exception {
		createOwner(validOwner()).andExpect(status().is2xxSuccessful());
	}

	@Test
	void functionalityStoresValidEmail() throws Exception {
		String email = uniqueEmail();
		ObjectNode o = validOwner();
		o.put("email", email);
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.email").value(email));
	}
}
