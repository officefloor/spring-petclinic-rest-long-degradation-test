package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp01: telephone is required. */
@Tag("cp01")
class Cp01Tests extends AcceptanceBase {

	@Test
	void coreCreatesWithValidTelephone() throws Exception {
		createOwner(validOwner()).andExpect(status().is2xxSuccessful());
	}

	@Test
	void errorRejectsBlankTelephone() throws Exception {
		ObjectNode o = validOwner();
		o.put("telephone", "");
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void errorRejectsMissingTelephone() throws Exception {
		ObjectNode o = validOwner();
		o.remove("telephone");
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void functionalityRejectsWhitespaceTelephone() throws Exception {
		ObjectNode o = validOwner();
		o.put("telephone", "   ");
		createOwner(o).andExpect(status().isBadRequest());
	}
}
